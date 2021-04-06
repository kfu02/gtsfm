/* Dependencies */
import React from 'react'
import Enzyme, { shallow } from 'enzyme'
import Adapter from 'enzyme-adapter-react-16'

/* Component to Test*/
import SfMDataDivNode from '../Components/SfMDataDivNode';

// Configure enzyme for react 16
Enzyme.configure({ adapter: new Adapter() })

describe('SfMDataDivNode.js Test', () => {

    /*  Passes in sample text and checks if the resulting SfMDataDivNode component is displaying the proper
        text.
    */
    it('Node displays `Node Testing` when that text is passed into props', () => {
        const sample_json = {'num': 50};
        const sampleFunction = () => console.log('sample function');
        const wrapper = shallow(<SfMDataDivNode 
                                    json={sample_json} 
                                    toggleDA_PC={sampleFunction} 
                                    textColor={'black'} 
                                    backgroundColor={'gray'} 
                                    topOffset={'10%'} 
                                    leftOffset={'10%'} 
                                    text={'Node Testing'}/>);
        const div = wrapper.find('div[id="Node Testing"]');
        expect(div.text()).toEqual('Node Testing');
    });

    /*  Passes in styling properties like textColor, backgroundColor, topOffset, and leftOffset and then
        checks if the resulting SfMDataDivNode component is styled properly.
    */
    it('Node has all the correct stylings passed in from props', () => {
        const sample_json = {'num': 50};
        const sampleFunction = () => console.log('sample function');
        const wrapper = shallow(<SfMDataDivNode 
                                    json={sample_json} 
                                    toggleDA_PC={sampleFunction} 
                                    textColor={'black'} 
                                    backgroundColor={'gray'} 
                                    topOffset={'10%'} 
                                    leftOffset={'20%'} 
                                    text={'Node Testing'}/>);

        const div = wrapper.find('div[id="Node Testing"]');
        expect(div.props().style.top).toEqual('10%');
        expect(div.props().style.left).toEqual('20%');
        expect(div.props().style.backgroundColor).toEqual('gray');
        expect(div.props().style.color).toEqual('black');
    });
})